/**
 * Business types supported at signup / onboarding (aligned with mobile + web `businessUi`).
 * `id` is stored as `settings.business_type`.
 */
export type SupportedIndustryId =
  | "retail"
  | "wholesale"
  | "restaurant"
  | "food"
  | "bakery"
  | "grocery"
  | "hotel"
  | "rental"
  | "salon"
  | "spa"
  | "fitness"
  | "healthcare"
  | "services"
  | "repair"
  | "cleaning"
  | "events"
  | "creator"
  | "support"
  | "general";

export type SupportedIndustry = {
  id: SupportedIndustryId;
  emoji: string;
  label: string;
  blurb: string;
};

export const SUPPORTED_INDUSTRIES: SupportedIndustry[] = [
  { id: "retail", emoji: "🛍️", label: "Retail & shops", blurb: "Physical or online store" },
  { id: "wholesale", emoji: "📦", label: "Wholesale / B2B", blurb: "Bulk orders & distribution" },
  { id: "grocery", emoji: "🛒", label: "Grocery / supermarket", blurb: "Fresh & packaged goods" },
  { id: "restaurant", emoji: "🍽️", label: "Restaurant / café", blurb: "Dine-in, takeaway, delivery" },
  { id: "food", emoji: "🥡", label: "Food delivery", blurb: "Kitchen & delivery-only" },
  { id: "bakery", emoji: "🍰", label: "Bakery", blurb: "Cakes, pastries, custom orders" },
  { id: "hotel", emoji: "🏨", label: "Hotel & lodging", blurb: "Rooms, guests, reservations" },
  { id: "rental", emoji: "🏠", label: "Rental / short-stay", blurb: "Properties, cars, equipment" },
  { id: "salon", emoji: "✂️", label: "Salon & beauty", blurb: "Hair, nails, beauty" },
  { id: "spa", emoji: "💆", label: "Spa & wellness", blurb: "Treatments & relaxation" },
  { id: "fitness", emoji: "🏋️", label: "Gym & fitness", blurb: "Memberships, classes, training" },
  { id: "healthcare", emoji: "🏥", label: "Healthcare / clinic", blurb: "Consultations & care" },
  { id: "services", emoji: "🔧", label: "Services / freelance", blurb: "IT, trades, consulting" },
  { id: "repair", emoji: "🛠️", label: "Repair & maintenance", blurb: "Electronics, appliances, vehicles" },
  { id: "cleaning", emoji: "🧹", label: "Cleaning services", blurb: "Home, office, commercial" },
  { id: "events", emoji: "📸", label: "Events & photography", blurb: "Events, shoots, productions" },
  { id: "creator", emoji: "🎨", label: "Creator / digital", blurb: "Courses, content, digital products" },
  { id: "support", emoji: "🎧", label: "Support & help desk", blurb: "Tickets & customer care" },
  { id: "general", emoji: "💬", label: "General / other", blurb: "NGO, info, anything else" },
];
