/**
 * Catalog / listing copy & field visibility by business type.
 * Aligned with mobile `ProductCatalogModal` categories and behaviour.
 */

export const CREATOR_CATEGORIES = [
  "Sponsored Post",
  "Instagram Reel",
  "Instagram Story",
  "TikTok Video",
  "YouTube Video",
  "Brand Ambassador",
  "Product Review",
  "Shoutout",
  "Photo Shoot",
  "Video Testimonial",
  "Live Stream",
  "Podcast Mention",
  "Blog Post",
  "Other",
];

export const RESTAURANT_CATEGORIES = [
  "Appetizers",
  "Main Course",
  "Desserts",
  "Beverages",
  "Breakfast",
  "Lunch Special",
  "Dinner Special",
  "Kids Menu",
  "Daily Special",
  "Other",
];

export const FOOD_CATEGORIES = [
  "Today's Special",
  "Rice Dishes",
  "Stews & Soups",
  "Grilled & BBQ",
  "Breakfast",
  "Snacks & Light Bites",
  "Combo Meals",
  "Beverages",
  "Salads & Sides",
  "Other",
];

export const BAKERY_CATEGORIES = [
  "Cakes",
  "Bread & Loaves",
  "Pastries & Croissants",
  "Cookies & Biscuits",
  "Cupcakes & Muffins",
  "Pies & Tarts",
  "Custom Orders",
  "Beverages",
  "Seasonal Specials",
  "Other",
];

export const GROCERY_CATEGORIES = [
  "Fresh Produce",
  "Dairy & Eggs",
  "Meat & Seafood",
  "Beverages",
  "Grains & Cereals",
  "Cooking Essentials",
  "Snacks & Confectionery",
  "Household & Cleaning",
  "Personal Care",
  "Baby & Kids",
  "Other",
];

export const WHOLESALE_CATEGORIES = [
  "Food & Beverages",
  "Electronics & Appliances",
  "Clothing & Textiles",
  "Beauty & Personal Care",
  "Household Products",
  "Industrial & Hardware",
  "Stationery & Office",
  "Agricultural Products",
  "Pharmaceutical",
  "Other",
];

export const RENTAL_CATEGORIES = [
  "Apartment",
  "House",
  "Car",
  "Equipment",
  "Venue",
  "Office Space",
  "Storage",
  "Vacation Rental",
  "Long-term Rental",
  "Other",
];

export const HEALTHCARE_CATEGORIES = [
  "Consultation",
  "Check-up",
  "Treatment",
  "Surgery",
  "Therapy",
  "Diagnostic",
  "Vaccination",
  "Emergency",
  "Follow-up",
  "Other",
];

export const FITNESS_CATEGORIES = [
  "Yoga",
  "Cardio",
  "Strength Training",
  "Pilates",
  "CrossFit",
  "Dance",
  "Martial Arts",
  "Swimming",
  "Group Class",
  "Personal Training",
  "Other",
];

export const SERVICES_CATEGORIES = [
  "Repair",
  "Installation",
  "Maintenance",
  "Consultation",
  "Support",
  "Training",
  "Inspection",
  "Cleaning",
  "Delivery",
  "Other",
];

export const SALON_CATEGORIES = [
  "Haircut",
  "Hair Color",
  "Styling",
  "Nails",
  "Facial",
  "Massage",
  "Waxing",
  "Makeup",
  "Treatment",
  "Other",
];

export const SPA_CATEGORIES = [
  "Swedish Massage",
  "Deep Tissue Massage",
  "Hot Stone Massage",
  "Facial",
  "Body Scrub",
  "Body Wrap",
  "Aromatherapy",
  "Couples Treatment",
  "Manicure & Pedicure",
  "Other",
];

export const CLEANING_CATEGORIES = [
  "Deep Clean",
  "Regular Clean",
  "Move In/Out Clean",
  "Office Cleaning",
  "Post-Construction",
  "Carpet & Upholstery",
  "Window Cleaning",
  "Other",
];

export const EVENTS_CATEGORIES = [
  "Wedding",
  "Birthday Party",
  "Corporate Event",
  "Graduation",
  "Baby Shower",
  "Product Launch",
  "Conference",
  "Portrait Session",
  "Other",
];

export const RETAIL_CATEGORIES = [
  "Electronics",
  "Clothing",
  "Food & Beverages",
  "Home & Garden",
  "Beauty & Health",
  "Sports & Outdoors",
  "Books & Media",
  "Toys & Games",
  "Automotive",
  "Other",
];

export const SUPPORT_CATEGORIES = [
  "Billing & Payments",
  "Technical Issues",
  "Account Management",
  "Orders & Delivery",
  "Returns & Refunds",
  "Getting Started",
  "Policies & Terms",
  "FAQs",
  "Complaints",
  "Other",
];

export const HOTEL_CATEGORIES = [
  "Standard Room",
  "Deluxe Room",
  "Superior Room",
  "Junior Suite",
  "Suite",
  "Executive Suite",
  "Villa",
  "Penthouse",
  "Family Room",
  "Twin Room",
];

export const GROCERY_UNITS = [
  "per piece",
  "per kg",
  "per g",
  "per packet",
  "per bottle",
  "per litre",
  "per dozen",
  "per bundle",
  "per box",
  "per bag",
];

export const WHOLESALE_UNITS = [
  "per carton",
  "per case",
  "per dozen",
  "per pallet",
  "per kg",
  "per bag",
  "per box",
  "per bundle",
  "per piece",
];

export interface ShopCatalogConfig {
  /** e.g. "Menu item", "Listing", "Service" */
  itemSingular: string;
  itemPlural: string;
  addButtonLabel: string;
  modalAddTitle: string;
  modalEditTitle: string;
  pageSubtitle: string;
  emptyTitle: string;
  emptyHint: string;
  nameLabel: string;
  namePlaceholder: string;
  categoryLabel: string;
  categoryPlaceholder: string;
  subCategoryLabel: string;
  subCategoryPlaceholder: string;
  descriptionPlaceholder: string;
  priceLabel: string;
  discountLabel: string;
  /** Suggestions for category `<datalist>` */
  categoryOptions: string[];
  showSubCategory: boolean;
  showDiscount: boolean;
  showStock: boolean;
  showUnitMoq: boolean;
  showPricingTiers: boolean;
  unitPlaceholder: string;
  unitSuggestions: string[];
  stockHelp?: string;
  advancedNote?: string;
}

const DEFAULT: ShopCatalogConfig = {
  itemSingular: "Product",
  itemPlural: "Products",
  addButtonLabel: "Add product",
  modalAddTitle: "Add product",
  modalEditTitle: "Edit product",
  pageSubtitle: "Manage what customers see in your shop. Share your link so they can browse and order.",
  emptyTitle: "No products yet",
  emptyHint: "Add your first product to start selling online.",
  nameLabel: "Name",
  namePlaceholder: "e.g. Premium wireless headphones",
  categoryLabel: "Category",
  categoryPlaceholder: "e.g. Electronics, Accessories",
  subCategoryLabel: "Sub-category",
  subCategoryPlaceholder: "e.g. Summer collection",
  descriptionPlaceholder: "Short description for customers…",
  priceLabel: "Price",
  discountLabel: "Sale price (optional)",
  categoryOptions: RETAIL_CATEGORIES,
  showSubCategory: false,
  showDiscount: true,
  showStock: true,
  showUnitMoq: false,
  showPricingTiers: false,
  unitPlaceholder: "",
  unitSuggestions: [],
  stockHelp: "Track whether this item is available.",
};

function cfg(p: Partial<ShopCatalogConfig>): ShopCatalogConfig {
  return { ...DEFAULT, ...p };
}

/**
 * Catalog UI for each business type (matches mobile catalog behaviour).
 */
export function getShopCatalogConfig(businessType: string): ShopCatalogConfig {
  const t = (businessType || "retail").toLowerCase();

  if (t === "restaurant") {
    return cfg({
      itemSingular: "Menu item",
      itemPlural: "Menu items",
      addButtonLabel: "Add menu item",
      modalAddTitle: "Add menu item",
      modalEditTitle: "Edit menu item",
      pageSubtitle: "Build your menu for the online shop. Customers browse by category.",
      emptyTitle: "Your menu is empty",
      emptyHint: "Add dishes and drinks so guests can order from your shop link.",
      nameLabel: "Item name",
      namePlaceholder: "e.g. Caesar Salad, House Burger",
      categoryLabel: "Menu section",
      categoryPlaceholder: "e.g. Main Course, Beverages",
      subCategoryLabel: "Sub-section (optional)",
      subCategoryPlaceholder: "e.g. Chef’s specials",
      descriptionPlaceholder: "Ingredients, allergens, spice level, sides…",
      priceLabel: "Price",
      categoryOptions: RESTAURANT_CATEGORIES,
      showSubCategory: true,
      showStock: true,
      advancedNote:
        "Sizes, add-ons, and modifier groups can be configured in the mobile app catalog.",
    });
  }

  if (t === "food") {
    return cfg({
      itemSingular: "Item",
      itemPlural: "Items",
      addButtonLabel: "Add item",
      modalAddTitle: "Add item",
      modalEditTitle: "Edit item",
      pageSubtitle: "List what you sell — combos, plates, and drinks.",
      emptyTitle: "Nothing listed yet",
      emptyHint: "Add food and drink items for your shop.",
      nameLabel: "Item name",
      namePlaceholder: "e.g. Jollof & chicken plate",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Combo meals, Beverages",
      subCategoryLabel: "Tag (optional)",
      subCategoryPlaceholder: "e.g. Spicy, Popular",
      descriptionPlaceholder: "What’s included, heat level, portion size…",
      priceLabel: "Price",
      categoryOptions: FOOD_CATEGORIES,
      showSubCategory: true,
      showStock: true,
      advancedNote:
        "Add-ons and bundles are available in the mobile app catalog.",
    });
  }

  if (t === "bakery") {
    return cfg({
      itemSingular: "Item",
      itemPlural: "Bakery items",
      addButtonLabel: "Add bakery item",
      modalAddTitle: "Add bakery item",
      modalEditTitle: "Edit bakery item",
      pageSubtitle: "Show cakes, bread, and pastries in your shop.",
      emptyTitle: "No bakery items yet",
      emptyHint: "Add products customers can pre-order or buy.",
      nameLabel: "Item name",
      namePlaceholder: "e.g. Chocolate layer cake (8\")",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Cakes, Bread",
      subCategoryLabel: "Details (optional)",
      subCategoryPlaceholder: "e.g. Custom orders only",
      descriptionPlaceholder: "Flavours, allergens, lead time…",
      priceLabel: "Price",
      categoryOptions: BAKERY_CATEGORIES,
      showSubCategory: true,
      showStock: true,
    });
  }

  if (t === "grocery") {
    return cfg({
      itemSingular: "Product",
      itemPlural: "Products",
      addButtonLabel: "Add product",
      modalAddTitle: "Add product",
      modalEditTitle: "Edit product",
      pageSubtitle: "Stock your online shelf with units and pack sizes.",
      emptyTitle: "No products yet",
      emptyHint: "Add grocery items with price per unit.",
      nameLabel: "Product name",
      namePlaceholder: "e.g. Fresh milk 1L",
      categoryLabel: "Aisle / category",
      categoryPlaceholder: "e.g. Dairy & Eggs",
      subCategoryLabel: "Brand / variant (optional)",
      subCategoryPlaceholder: "e.g. Full cream",
      descriptionPlaceholder: "Size, origin, expiry notes…",
      priceLabel: "Price (per unit below)",
      categoryOptions: GROCERY_CATEGORIES,
      showSubCategory: true,
      showStock: true,
      showUnitMoq: true,
      unitPlaceholder: "e.g. per litre, per kg",
      unitSuggestions: GROCERY_UNITS,
      stockHelp: "Optional count on hand for quick reference.",
    });
  }

  if (t === "wholesale") {
    return cfg({
      itemSingular: "SKU / line",
      itemPlural: "Wholesale lines",
      addButtonLabel: "Add line",
      modalAddTitle: "Add wholesale line",
      modalEditTitle: "Edit wholesale line",
      pageSubtitle: "List bulk products with MOQ and tier pricing.",
      emptyTitle: "No wholesale lines yet",
      emptyHint: "Add products with minimum order and volume pricing.",
      nameLabel: "Product name",
      namePlaceholder: "e.g. Sugar 50kg bag",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Food & Beverages",
      subCategoryLabel: "SKU note (optional)",
      subCategoryPlaceholder: "e.g. Brand, grade",
      descriptionPlaceholder: "Packaging, specs, lead time…",
      priceLabel: "Base price (list)",
      categoryOptions: WHOLESALE_CATEGORIES,
      showSubCategory: true,
      showDiscount: true,
      showStock: true,
      showUnitMoq: true,
      showPricingTiers: true,
      unitPlaceholder: "e.g. per carton, per pallet",
      unitSuggestions: WHOLESALE_UNITS,
      stockHelp: "Optional stock or availability note.",
    });
  }

  if (t === "rental") {
    return cfg({
      itemSingular: "Listing",
      itemPlural: "Listings",
      addButtonLabel: "Add listing",
      modalAddTitle: "Add listing",
      modalEditTitle: "Edit listing",
      pageSubtitle: "Publish rentals — homes, vehicles, gear, and venues.",
      emptyTitle: "No listings yet",
      emptyHint: "Add a listing with rate and description for guests.",
      nameLabel: "Listing title",
      namePlaceholder: "e.g. 2BR apartment — downtown",
      categoryLabel: "Listing type",
      categoryPlaceholder: "e.g. Apartment, Car",
      subCategoryLabel: "Area / zone (optional)",
      subCategoryPlaceholder: "e.g. Westlands",
      descriptionPlaceholder: "Amenities, rules, deposit, availability…",
      priceLabel: "Rate (e.g. per night / day)",
      discountLabel: "Promo rate (optional)",
      categoryOptions: RENTAL_CATEGORIES,
      showSubCategory: true,
      showDiscount: true,
      showStock: false,
    });
  }

  if (t === "hotel") {
    return cfg({
      itemSingular: "Room type",
      itemPlural: "Room types",
      addButtonLabel: "Add room type",
      modalAddTitle: "Add room type",
      modalEditTitle: "Edit room type",
      pageSubtitle: "List room categories and starting rates for your property.",
      emptyTitle: "No room types yet",
      emptyHint: "Add room categories guests can browse.",
      nameLabel: "Room name",
      namePlaceholder: "e.g. Deluxe Ocean View",
      categoryLabel: "Room category",
      categoryPlaceholder: "e.g. Deluxe Room",
      subCategoryLabel: "Floor / wing (optional)",
      subCategoryPlaceholder: "e.g. Tower A",
      descriptionPlaceholder: "Size, bed type, view, max guests…",
      priceLabel: "Starting rate (per night)",
      discountLabel: "Promo rate (optional)",
      categoryOptions: HOTEL_CATEGORIES,
      showSubCategory: true,
      showDiscount: true,
      showStock: true,
      stockHelp: "Optional: number of rooms in this category.",
    });
  }

  if (t === "salon" || t === "beauty") {
    return cfg({
      itemSingular: "Service",
      itemPlural: "Services",
      addButtonLabel: "Add service",
      modalAddTitle: "Add service",
      modalEditTitle: "Edit service",
      pageSubtitle: "List services and prices for clients booking online.",
      emptyTitle: "No services yet",
      emptyHint: "Add cuts, colour, nails, and other services.",
      nameLabel: "Service name",
      namePlaceholder: "e.g. Women’s haircut & blow-dry",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Haircut, Colour",
      subCategoryLabel: "Duration note (optional)",
      subCategoryPlaceholder: "e.g. ~45 min",
      descriptionPlaceholder: "What’s included, hair length, products used…",
      priceLabel: "Price",
      categoryOptions: SALON_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "spa") {
    return cfg({
      itemSingular: "Treatment",
      itemPlural: "Treatments",
      addButtonLabel: "Add treatment",
      modalAddTitle: "Add treatment",
      modalEditTitle: "Edit treatment",
      pageSubtitle: "Spa menu for online discovery and booking.",
      emptyTitle: "No treatments yet",
      emptyHint: "Add massages, facials, and packages.",
      nameLabel: "Treatment name",
      namePlaceholder: "e.g. Deep tissue 60 min",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Massage, Facial",
      subCategoryLabel: "Add-on note (optional)",
      subCategoryPlaceholder: "e.g. Hot stones",
      descriptionPlaceholder: "Benefits, duration, contraindications…",
      priceLabel: "Price",
      categoryOptions: SPA_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "healthcare" || t === "clinic") {
    return cfg({
      itemSingular: "Service",
      itemPlural: "Services",
      addButtonLabel: "Add service",
      modalAddTitle: "Add service",
      modalEditTitle: "Edit service",
      pageSubtitle: "List consultations and procedures patients can enquire about.",
      emptyTitle: "No services listed",
      emptyHint: "Add services with clear descriptions.",
      nameLabel: "Service name",
      namePlaceholder: "e.g. General consultation",
      categoryLabel: "Type",
      categoryPlaceholder: "e.g. Consultation, Treatment",
      subCategoryLabel: "Provider / dept (optional)",
      subCategoryPlaceholder: "e.g. Dr. Name",
      descriptionPlaceholder: "What to expect, preparation, duration…",
      priceLabel: "Price (or “from”)",
      categoryOptions: HEALTHCARE_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "fitness" || t === "gym") {
    return cfg({
      itemSingular: "Class / pass",
      itemPlural: "Classes & passes",
      addButtonLabel: "Add class or pass",
      modalAddTitle: "Add class or pass",
      modalEditTitle: "Edit class or pass",
      pageSubtitle: "Memberships, class packs, and drop-in rates.",
      emptyTitle: "Nothing listed yet",
      emptyHint: "Add classes or passes members can buy.",
      nameLabel: "Name",
      namePlaceholder: "e.g. Monthly unlimited",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Yoga, Membership",
      subCategoryLabel: "Schedule note (optional)",
      subCategoryPlaceholder: "e.g. Mon/Wed 6pm",
      descriptionPlaceholder: "What’s included, skill level, equipment…",
      priceLabel: "Price",
      categoryOptions: FITNESS_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "services" || t === "repair") {
    return cfg({
      itemSingular: "Service",
      itemPlural: "Services",
      addButtonLabel: "Add service",
      modalAddTitle: "Add service",
      modalEditTitle: "Edit service",
      pageSubtitle: "List jobs, repairs, and packages with pricing.",
      emptyTitle: "No services yet",
      emptyHint: "Add what you offer and typical pricing.",
      nameLabel: "Service name",
      namePlaceholder: "e.g. Laptop screen replacement",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Repair, Installation",
      subCategoryLabel: "Warranty note (optional)",
      subCategoryPlaceholder: "e.g. 90-day parts",
      descriptionPlaceholder: "Scope, parts, turnaround time…",
      priceLabel: "Price (estimate)",
      categoryOptions: SERVICES_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "cleaning") {
    return cfg({
      itemSingular: "Package",
      itemPlural: "Packages",
      addButtonLabel: "Add package",
      modalAddTitle: "Add package",
      modalEditTitle: "Edit package",
      pageSubtitle: "Cleaning packages and add-ons for quotes.",
      emptyTitle: "No packages yet",
      emptyHint: "Add standard packages clients can book.",
      nameLabel: "Package name",
      namePlaceholder: "e.g. Deep clean — 3 bedroom",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Deep Clean, Regular",
      subCategoryLabel: "Area (optional)",
      subCategoryPlaceholder: "e.g. Up to 120 sqm",
      descriptionPlaceholder: "What’s included, supplies, duration…",
      priceLabel: "From price",
      categoryOptions: CLEANING_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "events" || t === "photography") {
    return cfg({
      itemSingular: "Package",
      itemPlural: "Packages",
      addButtonLabel: "Add package",
      modalAddTitle: "Add package",
      modalEditTitle: "Edit package",
      pageSubtitle: "Event and creative packages for enquiries.",
      emptyTitle: "No packages yet",
      emptyHint: "List packages you sell or quote.",
      nameLabel: "Package name",
      namePlaceholder: "e.g. Wedding full day coverage",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. Wedding, Corporate",
      subCategoryLabel: "Deliverables (optional)",
      subCategoryPlaceholder: "e.g. Photos + video",
      descriptionPlaceholder: "Hours, deliverables, travel…",
      priceLabel: "Package price (or from)",
      categoryOptions: EVENTS_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "creator") {
    return cfg({
      itemSingular: "Offering",
      itemPlural: "Offerings",
      addButtonLabel: "Add offering",
      modalAddTitle: "Add offering",
      modalEditTitle: "Edit offering",
      pageSubtitle: "Sponsorship tiers, content formats, and rates for brands.",
      emptyTitle: "No offerings yet",
      emptyHint: "Add packages creators can pitch or sell.",
      nameLabel: "Offering name",
      namePlaceholder: "e.g. Instagram Reel + story set",
      categoryLabel: "Format",
      categoryPlaceholder: "e.g. Reel, Sponsored post",
      subCategoryLabel: "Audience note (optional)",
      subCategoryPlaceholder: "e.g. 50k followers, niche",
      descriptionPlaceholder: "Deliverables, usage rights, turnaround…",
      priceLabel: "Rate",
      categoryOptions: CREATOR_CATEGORIES,
      showSubCategory: true,
      showStock: false,
    });
  }

  if (t === "support") {
    return cfg({
      itemSingular: "Article",
      itemPlural: "Knowledge items",
      addButtonLabel: "Add article",
      modalAddTitle: "Add knowledge article",
      modalEditTitle: "Edit knowledge article",
      pageSubtitle: "Structured topics customers and AI can reference.",
      emptyTitle: "No articles yet",
      emptyHint: "Add short knowledge base entries.",
      nameLabel: "Title",
      namePlaceholder: "e.g. How to reset password",
      categoryLabel: "Topic",
      categoryPlaceholder: "e.g. Account",
      subCategoryLabel: "Tags (optional)",
      subCategoryPlaceholder: "e.g. login, security",
      descriptionPlaceholder: "Summary or answer text…",
      priceLabel: "Amount (use 0)",
      discountLabel: "",
      categoryOptions: SUPPORT_CATEGORIES,
      showSubCategory: true,
      showDiscount: false,
      showStock: false,
      stockHelp: "Pricing is not used for support articles — leave amount at 0.",
    });
  }

  if (t === "general" || t === "other") {
    return cfg({
      itemSingular: "Item",
      itemPlural: "Items",
      addButtonLabel: "Add item",
      modalAddTitle: "Add item",
      modalEditTitle: "Edit item",
      pageSubtitle: "List what you sell or offer online.",
      emptyTitle: "Nothing listed yet",
      emptyHint: "Add an item with name, price, and description.",
      nameLabel: "Name",
      namePlaceholder: "e.g. Consultation, Product name",
      categoryLabel: "Category",
      categoryPlaceholder: "e.g. General",
      subCategoryLabel: "Details (optional)",
      subCategoryPlaceholder: "",
      descriptionPlaceholder: "Describe what customers get…",
      priceLabel: "Price",
      categoryOptions: [...RETAIL_CATEGORIES],
      showSubCategory: true,
      showStock: true,
    });
  }

  // Default: retail-style products
  return cfg({
    itemSingular: "Product",
    itemPlural: "Products",
    addButtonLabel: "Add product",
    modalAddTitle: "Add product",
    modalEditTitle: "Edit product",
    pageSubtitle:
      "Manage your storefront. Share your shop link so customers browse and order.",
    emptyTitle: "No products yet",
    emptyHint: "Add products with photos from the mobile app.",
    nameLabel: "Product name",
    namePlaceholder: 'e.g. Samsung TV 43", Leather bag',
    categoryLabel: "Category",
    categoryPlaceholder: "e.g. Electronics, Clothing",
    subCategoryLabel: "Collection / variant (optional)",
    subCategoryPlaceholder: "e.g. 2025 line",
    descriptionPlaceholder: "Features, sizing, warranty…",
    priceLabel: "Price",
    categoryOptions: RETAIL_CATEGORIES,
    showSubCategory: true,
    showDiscount: true,
    showStock: true,
    advancedNote: "Multiple images and product variants are available in the mobile app.",
  });
}
